FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pawquanta.py .
COPY Pawquanta-research/chonk_hash.py Pawquanta-research/chonk_hash.py
COPY Pawquanta-research/assets/mascot.jpg Pawquanta-research/assets/mascot.jpg
RUN useradd --create-home pqua && mkdir /data && chown pqua:pqua /data
USER pqua
ENTRYPOINT ["python", "pawquanta.py", "node", "--bind", "0.0.0.0", "--port", "18701", "--data", "/data/chain.json"]
