import logging
import os
from fastapi import HTTPException
from modules.loaders import LOADERS
import yake
import re
import torch


def IndexDocuments(brain, project, documents):
    docs = brain.text_splitter.split_documents(documents)

    texts = [doc.page_content for doc in docs]
    metadatas = [doc.metadata for doc in docs]
 
    for metadata in metadatas:
      for key, value in list(metadata.items()):
          if key == 'languages' or value is None:
              del metadata[key]

    ids = project.db.add_texts(texts=texts, metadatas=metadatas)
    return ids


def ExtractKeywordsForMetadata(documents):
    max_ngram_size = 4
    numOfKeywords = 15
    kw_extractor = yake.KeywordExtractor(n=max_ngram_size, top=numOfKeywords)
    for document in documents:
        metadataKeywords = ""
        keywords = kw_extractor.extract_keywords(document.page_content)
        for kw in keywords:
            metadataKeywords = metadataKeywords + kw[0] + ", "
        document.metadata["keywords"] = metadataKeywords

    return documents


def FindFileLoader(filepath, ext, eargs={}):
    if ext in LOADERS:
        loader_class, loader_args = LOADERS[ext]
        loader_args.update(eargs)
        return loader_class(filepath, **loader_args)
    else:
        raise Exception("Invalid file type.")


def FindEmbeddingsPath(projectName):
    embeddings_path = os.environ["EMBEDDINGS_PATH"]
    project_dirs = [d for d in os.listdir(
        embeddings_path) if os.path.isdir(os.path.join(embeddings_path, d))]

    for dir in project_dirs:
        if re.match(f'^{projectName}_[0-9]+$', dir):
            return os.path.join(embeddings_path, dir)

    return None


def loadEnvVars():
    if "EMBEDDINGS_PATH" not in os.environ:
        os.environ["EMBEDDINGS_PATH"] = "./embeddings/"

    if "UPLOADS_PATH" not in os.environ:
        os.environ["UPLOADS_PATH"] = "./uploads/"

    if "ANONYMIZED_TELEMETRY" not in os.environ:
        os.environ["ANONYMIZED_TELEMETRY"] = "False"

    if "LOG_LEVEL" not in os.environ:
        os.environ["LOG_LEVEL"] = "INFO"

    os.environ["ALLOW_RESET"] = "true"


def print_cuda_mem():
    print("Allocated: " +
          (torch.cuda.memory_allocated() /
           1e6) +
          "MB, Max: " +
          (torch.cuda.max_memory_allocated() /
           1e6) +
          " MB, Reserved:" +
          (torch.cuda.memory_reserved() /
              1e6) +
          "MB")


def get_logger(name, level=logging.INFO):
    """To setup as many loggers as you want"""

    handler = logging.FileHandler("./logs/" + name + ".log") 
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger