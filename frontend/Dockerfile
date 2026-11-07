# The app is built once and served as static files by Caddy, which also forwards the API to the backend
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM caddy:2-alpine
COPY Caddyfile site.caddy /etc/caddy/
COPY --chmod=755 https.sh /usr/local/bin/https.sh
COPY --from=build /app/dist /srv
EXPOSE 5173
# Caddy, plus the HTTPS configuration chosen in Settings › HTTPS (https.sh)
CMD ["/usr/local/bin/https.sh"]
