FROM python:3.8.7-slim

COPY requirements.txt ./

RUN apt-get update \
    # Can't find wheels for asyncpg for some reason :(
    && apt-get install --no-install-recommends -y libpq-dev gcc \
    && pip install -r requirements.txt \
    && apt remove -y libpq-dev gcc \
    && apt -y autoremove \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

COPY test/ /example/test/
COPY main.py /example

CMD [ "python", "/example/main.py" ]
