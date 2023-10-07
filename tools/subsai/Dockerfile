#FROM python:3.10.6
FROM pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime

WORKDIR /subsai

COPY requirements.txt .

ENV DEBIAN_FRONTEND noninteractive
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y git && \
    apt-get -y install gcc mono-mcs && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml .
COPY ./assets ./assets
COPY ./src ./src

RUN pip install .
EXPOSE 8501
EXPOSE 5678
# ENV LD_LIBRARY_PATH=/opt/conda/lib/python3.10/site-packages/torch/lib/libcudnn_ops_infer.so.8:$LD_LIBRARY_PATH
CMD ["sh", "-c", "LD_LIBRARY_PATH=/opt/conda/lib/python3.10/site-packages/torch/lib:$LD_LIBRARY_PATH python src/subsai/webui.py"]

