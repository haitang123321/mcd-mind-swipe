FROM python:3.12-slim

WORKDIR /app
COPY services/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/api ./services/api
COPY data/mock_menu.json ./data/mock_menu.json

WORKDIR /app/services/api
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
