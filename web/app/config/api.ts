// API 服务器配置
// ponytail: 开发环境直连 localhost:8000, 生产通过 nginx 反向代理

export const API_BASE = import.meta.dev
  ? 'http://localhost:8000'
  : ''

export const WS_BASE = import.meta.dev
  ? 'ws://localhost:8000'
  : `wss://${window.location.host}`
