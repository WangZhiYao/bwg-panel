# ---------- Stage 1：构建前端 ----------
FROM node:22-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build          # vue-tsc 类型检查 + vite build → /build/dist

# ---------- Stage 2：运行时 ----------
FROM python:3.12-slim
RUN useradd --system --no-create-home --shell /usr/sbin/nologin bwgpanel
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
# 路径须匹配 main.py 的 _FRONTEND_DIST 推导：backend/ 与 frontend/dist 同级
COPY --from=frontend-build /build/dist /app/frontend/dist

ENV DB_PATH=/data/panel.db \
    PYTHONUNBUFFERED=1
RUN mkdir -p /data && chown -R bwgpanel:bwgpanel /data /app
USER bwgpanel
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["python", "-m", "app", "--host", "0.0.0.0", "--port", "8000"]
