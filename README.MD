# 📸 Screenshot API

API REST construída com **FastAPI** e **Playwright** que recebe uma URL e retorna um screenshot da página em formato **Base64**.

---

## 🚀 Tecnologias

- [Python 3.11+](https://www.python.org/)
- [FastAPI](https://fastapi.tiangolo.com/) — framework web moderno e de alta performance
- [Playwright](https://playwright.dev/python/) — automação de browser para captura de screenshots
- [Uvicorn](https://www.uvicorn.org/) — servidor ASGI

---

## 📋 Pré-requisitos

- Python **3.11.8** (via [pyenv](https://github.com/pyenv/pyenv) recomendado)
- pip instalado

---

## ⚙️ Instalação

### 1. Selecione a versão correta do Python (se usar pyenv)

```bash
pyenv shell 3.11.8
```

### 2. Instale as dependências

```bash
pip install -r requirements.txt
```

### 3. Instale os browsers do Playwright

> ⚠️ Se estiver em uma rede corporativa com certificado SSL customizado, use:

```bash
NODE_TLS_REJECT_UNAUTHORIZED=0 python -m playwright install chromium
```

> Em redes sem restrição SSL:

```bash
python -m playwright install chromium
```

---

## ▶️ Executando

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

A API estará disponível em: `http://localhost:8000`

---

## 📡 Endpoints

### `GET /screenshot`

Captura um screenshot de uma URL e retorna a imagem em Base64.

**Query Parameters:**

| Parâmetro | Tipo   | Obrigatório | Descrição                     |
| --------- | ------ | ----------- | ----------------------------- |
| `url`     | string | ✅ Sim      | URL da página a ser capturada |

**Exemplo de requisição:**

```
GET http://localhost:8000/screenshot?url=https://google.com
```

**Exemplo de resposta:**

```json
{
  "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
}
```

---

## 📖 Documentação interativa

Com o servidor rodando, acesse:

- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
