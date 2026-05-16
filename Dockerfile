FROM python:3.11-slim

WORKDIR /app

COPY src/ /app

RUN pip install --no-cache-dir \
    "fastapi==0.109.2" \
    "uvicorn==0.27.0" \
    "pydantic==2.6.0" \
    "python-dotenv==1.0.0" \
    "requests==2.31.0" \
    "langchain==0.2.16" \
    "langchain-openai==0.1.23" \
    "langchain-core==0.2.38" \
    "langchain-community==0.2.16" \
    "click==8.1.7" \
    "pdfplumber>=0.10.0" \
    "pypdf>=3.0.0" \
    "python-docx>=1.0.0"

ENV PYTHONUNBUFFERED=1

CMD ["python", "__main__.py", "--host", "0.0.0.0", "--port", "5000"]
