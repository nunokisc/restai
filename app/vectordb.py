import os
import shutil
from langchain.vectorstores import Chroma, FAISS, Redis
import redis

from app.tools import FindEmbeddingsPath


def vector_init(brain, project):
    path = FindEmbeddingsPath(project.model.name)

    if project.model.vectorstore == "chroma":
        return Chroma(
            persist_directory=path, embedding_function=brain.getEmbedding(
                project.model.embeddings))
    elif project.model.vectorstore == "faiss":
        if path is None or len(os.listdir(path)) == 0:
            return FAISS(embedding_function=brain.getEmbedding(
                project.model.embeddings))
        else:
            return vector_load(brain, project)
    elif project.model.vectorstore == "redis":
        if path is None or len(os.listdir(path)) == 0:
            schema = {'text': [{'name': 'source'}, {'name': 'keywords'}]}
            return Redis(
                redis_url="redis://" +
                os.environ["REDIS_HOST"] +
                ":" +
                os.environ["REDIS_PORT"],
                index_name=project.model.name,
                embedding=brain.getEmbedding(
                    project.model.embeddings),
                index_schema=schema)
        else:
            return vector_load(brain, project)


def vector_save(project):
    if project.model.vectorstore == "faiss":
        project.db.save_local(FindEmbeddingsPath(
            project.model.name))
    elif project.model.vectorstore == "chroma":
        project.db.persist()
    elif project.model.vectorstore == "redis":
        project.db.write_schema(FindEmbeddingsPath(
            project.model.name) + "/schema.yaml")


def vector_load(brain, project):
    if project.model.vectorstore == "faiss":
        return FAISS.load_local(FindEmbeddingsPath(
            project.model.name), brain.getEmbedding(
            project.model.embeddings))
    elif project.model.vectorstore == "redis":
        return Redis.from_existing_index(
            brain.getEmbedding(
                project.model.embeddings),
            index_name=project.model.name,
            redis_url="redis://" +
            os.environ["REDIS_HOST"] +
            ":" +
            os.environ["REDIS_PORT"],
            schema=FindEmbeddingsPath(
                project.model.name) +
            "/schema.yaml")


def vector_list(project, type="all"):
    urls = []
    files = []
    other = []
    if project.model.vectorstore == "chroma":
        collection = project.db._client.get_collection("langchain")

        docs = collection.get(
            include=["metadatas"]
        )

        for metadata in docs["metadatas"]:
            if type == "url" or type == "urls":
                if metadata["source"].startswith(
                        ('http://', 'https://')) and metadata["source"] not in urls:
                    urls.append(metadata["source"])
            elif type == "other":
                if not metadata["source"].startswith(
                        ('http://', 'https://')) and metadata["source"] not in other:
                    other.append(metadata["source"])
            elif type == "all":
                if metadata["source"].startswith(
                        ('http://', 'https://')) and metadata["source"] not in urls:
                    urls.append(metadata["source"])
                if not metadata["source"].startswith(
                        ('http://', 'https://')) and metadata["source"] not in other:
                    other.append(metadata["source"])

    elif project.model.vectorstore == "redis":
        lredis = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=os.environ["REDIS_PORT"],
            decode_responses=True)
        keys = lredis.keys(project.db.key_prefix + "*")
        for key in keys:
            source = lredis.hget(key, "source")
            if type == "url" or type == "urls":
                if source.startswith(
                        ('http://', 'https://')) and source not in urls:
                    urls.append(source)
            elif type == "other" or type == "others":
                if not source.startswith(
                        ('http://', 'https://')) and source not in other:
                    other.append(source)
            elif type == "all":
                if source.startswith(
                        ('http://', 'https://')) and source not in urls:
                    urls.append(source)
                if not source.startswith(
                        ('http://', 'https://')) and source not in other:
                    other.append(source)

    return {"urls": urls, "other": other}


def vector_info(project):
    if project.model.vectorstore == "chroma":
        dbInfo = project.db.get()
        return len(dbInfo["documents"]), len(dbInfo["metadatas"])
    elif project.model.vectorstore == "redis":
        lredis = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=os.environ["REDIS_PORT"],
            decode_responses=True)
        keys = lredis.keys(project.db.key_prefix + "*")
        return len(keys), len(keys)


def vector_find(project, source):
    docs = []
    if project.model.vectorstore == "chroma":
        collection = project.db._client.get_collection("langchain")
        docs = collection.get(where={'source': source})
    elif project.model.vectorstore == "redis":
        lredis = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=os.environ["REDIS_PORT"],
            decode_responses=True)
        keys = lredis.keys(project.db.key_prefix + "*")
        ids = []
        metadatas = []
        documents = []
        for key in keys:
            lsource = lredis.hget(key, "source")
            if lsource == source:
                ids.append(key)
                metadatas.append(
                    {"source": lsource, "keywords": lredis.hget(key, "keywords")})
                documents.append(lredis.hget(key, "content"))

        docs = {"ids": ids, "metadatas": metadatas, "documents": documents}

    return docs


def vector_delete(project):
    if project.model.vectorstore == "chroma":
        try:
            embeddingsPath = FindEmbeddingsPath(project.model.name)
            shutil.rmtree(embeddingsPath, ignore_errors=True)
        except BaseException:
            pass
    elif project.model.vectorstore == "redis":
        project.db.drop_index(project.model.name, delete_documents=True, redis_url="redis://" +
                              os.environ["REDIS_HOST"] +
                              ":" +
                              os.environ["REDIS_PORT"])
        try:
            embeddingsPath = FindEmbeddingsPath(project.model.name)
            shutil.rmtree(embeddingsPath, ignore_errors=True)
        except BaseException:
            pass


def vector_delete_source(project, source):
    ids = []
    if project.model.vectorstore == "chroma":
        collection = project.db._client.get_collection("langchain")
        ids = collection.get(where={'source': source})['ids']
        if len(ids):
            collection.delete(ids)
    elif project.model.vectorstore == "redis":
        lredis = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=os.environ["REDIS_PORT"],
            decode_responses=True)
        keys = lredis.keys(project.db.key_prefix + "*")
        for key in keys:
            lsource = lredis.hget(key, "source")
            if lsource == source or lsource == os.path.join(
                    os.environ["UPLOADS_PATH"], project.model.name, source):
                ids.append(key)
                lredis.delete(key)
    return ids


def vector_delete_id(project, id):
    if project.model.vectorstore == "chroma":
        collection = project.db._client.get_collection("langchain")
        ids = collection.get(ids=[id])['ids']
        if len(ids):
            collection.delete(ids)
    elif project.model.vectorstore == "redis":
        lredis = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=os.environ["REDIS_PORT"],
            decode_responses=True)
        lredis.delete(id)
    return id


def vector_reset(brain, project):
    if project.model.vectorstore == "chroma":
        project.db._client.reset()
    elif project.model.vectorstore == "redis":
        project.db.drop_index(project.model.name, delete_documents=True, redis_url="redis://" +
                              os.environ["REDIS_HOST"] +
                              ":" +
                              os.environ["REDIS_PORT"])

    project.db = vector_init(brain, project)
