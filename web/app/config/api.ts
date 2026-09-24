// API 服务器配置
// ponytail: 开发环境直连 localhost:8000, 生产通过 nginx 反向代理

export const API_BASE = import.meta.dev
  ? 'http://localhost:8000'
  : ''

// WebSocket 地址。
// 开发: 直连后端 8000。
// 容器部署: 原实现为 `wss://${window.location.host}`, 有两个问题:
//   1) 页面以 http 访问, 用 wss 会 TLS 握手失败;
//   2) nuxt 容器自身不提供 /api/v1/system/seed/ws (该端点在 api 容器上),
//      依赖 nitro 代理转发 WS 升级不可靠。
// 因此改由构建期注入 VITE_WS_ORIGIN (见 docker/Dockerfile.web) 指向宿主机暴露的
// 后端端口; 未注入时按当前页面的协议回落到同源地址。
const injectedWsOrigin = import.meta.env.VITE_WS_ORIGIN

export const WS_BASE = injectedWsOrigin
  ? String(injectedWsOrigin)
  : (import.meta.dev
      ? 'ws://localhost:8000'
      : `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`)
