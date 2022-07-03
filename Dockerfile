FROM python:3.10-buster

WORKDIR /app

COPY src .
COPY poetry.lock .
COPY pyproject.toml .

RUN python3 -m pip install poetry
RUN poetry config virtualenvs.create false
RUN poetry install --no-dev

ENTRYPOINT [ "nftmeow" ]