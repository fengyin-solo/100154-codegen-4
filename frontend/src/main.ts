import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { setOperatorContext } from './api/client'
import { useSessionStore } from './stores/session'
import './styles/global.css'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)

// 请求头里的操作人身份始终跟随会话状态，保证越权判断用的是当前身份。
const session = useSessionStore(pinia)
setOperatorContext({ name: session.operator, role: session.role })
session.$subscribe((_, state) => {
  setOperatorContext({ name: state.operator, role: state.role })
})

app.mount('#app')
