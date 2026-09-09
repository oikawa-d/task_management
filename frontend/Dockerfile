FROM node:26-alpine AS builder
WORKDIR /app
ARG VITE_API_BASE_URL=/api
ARG VITE_USER_NAME_MAX_LENGTH=30
ARG VITE_PASSWORD_MIN_LENGTH=8
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_USER_NAME_MAX_LENGTH=$VITE_USER_NAME_MAX_LENGTH
ENV VITE_PASSWORD_MIN_LENGTH=$VITE_PASSWORD_MIN_LENGTH
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine AS runtime
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK CMD wget -qO- http://localhost:80/ || exit 1
