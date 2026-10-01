FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 3001
VOLUME ["/app/sessions"]

CMD ["npm", "start"]
