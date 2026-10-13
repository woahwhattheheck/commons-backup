FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir numpy safetensors "git+https://github.com/trycua/cua.git@9bbfa7dd3e27ca7f1861ede70aaca390174493f9#subdirectory=libs/cua-s1/python"
WORKDIR /app
COPY host/cua_s1_cloud/server.py /app/server.py
ENV PORT=8080 CUA_S1_MODEL_DIR=/models
EXPOSE 8080
CMD ["python", "/app/server.py"]
