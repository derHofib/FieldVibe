FROM node:22-alpine AS base
WORKDIR /app
COPY package*.json ./

FROM base AS deps
RUN npm install

FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

FROM deps AS build
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ARG VITE_MAPBOX_TOKEN=
ENV VITE_MAPBOX_TOKEN=$VITE_MAPBOX_TOKEN
COPY . .
RUN npm run build

FROM node:22-alpine AS production
WORKDIR /app
RUN npm install -g serve@14
COPY --from=build /app/dist ./dist
# Security-Header fuer den Betrieb ohne Caddy (.ip.yml); hinter Caddy
# ueberschreibt dessen header-Direktive dieselben Felder. Bewusst ohne HSTS
# (HTTP) und ohne CSP (API-/MinIO-Host sind im IP-Modus nicht vorab bekannt).
# serve loest -c relativ zum Auslieferungsordner (dist) auf -- daher absoluter Pfad.
COPY serve.json ./serve.json
EXPOSE 4173
CMD ["serve", "-s", "dist", "-l", "4173", "-c", "/app/serve.json"]
