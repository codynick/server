FROM python:3.12-slim
WORKDIR /workspace
COPY CodyNick.py Dashboard.py SpriteStage.py /opt/codynick/
ENV PYTHONPATH=/opt/codynick PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 10000:10000
CMD ["python", "-u", "/workspace/main.py"]
