# The app is built once and served as static files by Caddy, which also forwards the API to the backend
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Caddy with the redirect from HTTP to HTTPS on the same port that browsers don't store (caddy/redirect.go)
FROM caddy:2-builder-alpine AS caddy
COPY caddy /src/redirect
RUN xcaddy build --with candidate/caddy/redirect=/src/redirect --output /usr/bin/caddy-candidate

FROM caddy:2-alpine
COPY --from=caddy /usr/bin/caddy-candidate /usr/bin/caddy
COPY Caddyfile site.caddy /etc/caddy/
COPY --chmod=755 https.sh /usr/local/bin/https.sh
COPY --from=build /app/dist /srv
EXPOSE 5173
# Caddy, plus the HTTPS configuration chosen in Settings › Security › HTTPS (https.sh)
CMD ["/usr/local/bin/https.sh"]
