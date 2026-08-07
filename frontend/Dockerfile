FROM node:24-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
ARG VITE_API_URL=
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY default.conf.template /etc/nginx/templates/default.conf.template
ENV PORT=80 \
    BACKEND_HOSTPORT=backend:8000 \
    NGINX_ENVSUBST_FILTER="^(PORT|BACKEND_HOSTPORT)$"
EXPOSE 80
