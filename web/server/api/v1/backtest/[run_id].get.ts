import { proxyRequest, defineEventHandler } from 'h3'

export default defineEventHandler((event) => {
  return proxyRequest(event, `http://localhost:8000${event.path}`)
})
