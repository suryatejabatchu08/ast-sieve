FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml README.md ./
COPY ast_sieve ./ast_sieve
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim
COPY --from=build /install /usr/local
WORKDIR /code
ENTRYPOINT ["ast-sieve"]
CMD ["scan", "."]
