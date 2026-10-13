FROM python:3.12-slim
WORKDIR /app
COPY acqatlas.py /app/acqatlas.py
COPY fixtures /app/fixtures
USER 65534:65534
ENTRYPOINT ["python", "/app/acqatlas.py"]
CMD ["--help"]
