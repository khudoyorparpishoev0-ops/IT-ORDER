# --- Сборка ---
FROM node:22-alpine AS build
WORKDIR /app

# Слой зависимостей отдельно: пересобирается только при смене lock-файла.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# --- Раздача ---
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
