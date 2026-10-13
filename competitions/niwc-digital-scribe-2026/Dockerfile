FROM python:3.13-slim
WORKDIR /app
COPY _engine.py /app/_engine.py
COPY workbench.py /app/workbench.py
COPY fixtures/synthetic_exercise.json /app/fixtures/synthetic_exercise.json
ENTRYPOINT ["python", "/app/workbench.py"]
CMD ["compile", "/app/fixtures/synthetic_exercise.json"]
