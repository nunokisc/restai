import os
from fastapi import HTTPException
from langchain.text_splitter import CharacterTextSplitter, RecursiveCharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.chains import ConversationalRetrievalChain, LLMChain
from langchain.vectorstores import Chroma

from app.models import EmbeddingModel, IngestModel, ProjectModel, ProjectModelUpdate, QuestionModel, ChatModel
from app.project import Project
from app.tools import FindEmbeddingsPath
from modules.embeddings import EMBEDDINGS
from modules.llms import LLMS
from app.database import dbc


class Brain:
    def __init__(self):
        self.projects = []
        self.llmCache = {}
        self.embeddingCache = {}

        self.text_splitter = RecursiveCharacterTextSplitter(
            separators=[" "], chunk_size=1024, chunk_overlap=30)

    def getLLM(self, llmModel, **kwargs):
        if llmModel in self.llmCache:
            return self.llmCache[llmModel]
        else:
            if llmModel in LLMS:
                llm_class, llm_args = LLMS[llmModel]
                llm = llm_class(**llm_args, **kwargs)
                self.llmCache[llmModel] = llm
                return llm
            else:
                raise Exception("Invalid LLM type.")

    def getEmbedding(self, embeddingModel):
        if embeddingModel in self.embeddingCache:
            return self.embeddingCache[embeddingModel]
        else:
            if embeddingModel in EMBEDDINGS:
                embedding_class, embedding_args = EMBEDDINGS[embeddingModel]
                model = embedding_class(**embedding_args)
                self.embeddingCache[embeddingModel] = model
                return model
            else:
                raise Exception("Invalid Embedding type.")

    def findProject(self, name, db):
        for project in self.projects:
            if project.model.name == name:
                return project

        p = dbc.get_project_by_name(db, name)
        if p is None:
            return None
        proj = ProjectModel.model_validate(p)
        if proj is not None:
            project = Project()
            project.model = proj
            self.initializeEmbeddings(project)
            self.projects.append(project)
            return project

    def createProject(self, projectModel, db):
        dbc.create_project(
            db,
            projectModel.name,
            projectModel.embeddings,
            projectModel.llm,
            projectModel.system)
        project = Project()
        project.boot(projectModel)
        self.initializeEmbeddings(project)
        self.projects.append(project)

    def initializeEmbeddings(self, project):
        project.db = Chroma(
            persist_directory=FindEmbeddingsPath(
                project.model.name), embedding_function=self.getEmbedding(
                project.model.embeddings))

    def editProject(self, name, projectModel: ProjectModelUpdate, db):
        project = self.findProject(name, db)
        if project is None:
            return False

        proj_db = dbc.get_project_by_name(db, name)
        if proj_db is None:
            raise Exception("Project not found")

        changed = False
        if projectModel.llm is not None and proj_db.llm != projectModel.llm:
            proj_db.llm = projectModel.llm
            changed = True

        if proj_db.system != projectModel.system:
            proj_db.system = projectModel.system
            changed = True

        if changed:
            dbc.update_project(db)
            project.model = ProjectModel.model_validate(proj_db)

        return project

    def deleteProject(self, name, db):
        self.findProject(name, db)
        dbc.delete_project(db, dbc.get_project_by_name(db, name))
        proj = self.findProject(name, db)
        if proj is not None:
            proj.delete()
            self.projects.remove(proj)
        return True


    def question(self, project, questionModel):
        llm = self.getLLM(questionModel.llm or project.model.llm)

        retriever = project.db.as_retriever(
            search_type="similarity_score_threshold", search_kwargs={"score_threshold": questionModel.score or .6, "k": questionModel.k or 4}
        )

        qa = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=retriever,
        )

        return qa.run(questionModel.question).strip()


    def chat(self, project, chatModel):
        llm = self.getLLM(project.model.llm)
        chat = project.loadChat(chatModel)

        retriever = project.db.as_retriever(
            search_type="similarity_score_threshold", search_kwargs={"score_threshold": chatModel.score or .6, "k": chatModel.k or 4}
        )

        conversationalChain = ConversationalRetrievalChain.from_llm(
            llm=llm, retriever=retriever
        )

        result = conversationalChain(
            {"question": chatModel.message, "chat_history": chat.history}
        )
        chat.history.append((chatModel.message, result["answer"]))
        return chat, result["answer"].strip()


    def questionContext(self, project, questionModel):
        llm = self.getLLM(questionModel.llm or project.model.llm)

        default_system = "You are a digital assistant, answer the question about the following context. NEVER invent an answer, if you don't know the answer, just say you don't know. If you don't understand the question, just say you don't understand."

        prompt_template = """{system}
            Confine your answer within the given context and do not generate the next context.
    Answer truthful answers, don't try to make up an answer.
    
            Question: {{question}}
            =========
            Context: {{context}}
            =========
            Answer:""".format(system=questionModel.system or project.model.system or default_system)

        prompt = PromptTemplate(
            template=prompt_template, input_variables=["context", "question"]
        )
        chain = LLMChain(llm=llm, prompt=prompt)

        retriever = project.db.as_retriever(
            search_type="similarity_score_threshold", search_kwargs={"score_threshold": questionModel.score or .6, "k": questionModel.k or 4}
        )
        
        try:
            docs = retriever.get_relevant_documents(questionModel.question)
        except BaseException:
            docs = []

        if len(docs) == 0:
            inputs = [{"context": "",
                       "question": questionModel.question}]
        else:
            inputs = [{"context": doc.page_content,
                       "question": questionModel.question} for doc in docs]

        output = chain.apply(inputs)
        return output[0]["text"].strip(), len(docs)
