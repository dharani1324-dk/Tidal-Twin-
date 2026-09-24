# TidalTwin - Frontend Image
# Stage 1: build the React app
# Stage 2: serve it with nginx and proxy /api to the backend
# -----------------------------------------------------------
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

# In production, calls go through nginx -> backend, so the API lives
# on the SAME origin. Empty base URL = same origin.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

# Runs the full pipeline (Cesium asset copy + tsc typecheck + vite build).
# Any failure here fails the image, by design.
RUN npm run build

FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]