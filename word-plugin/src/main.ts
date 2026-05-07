import './index.css'
import { createApp } from 'vue'
import App from './App.vue'
import { i18n } from './i18n'
import router from './router'

window.Office.onReady(async () => {
  const app = createApp(App)
  const fullPath = Office.context.document.url;

  function getFileDirectory(fullPath) {
    if (!fullPath) return null;
    const lastSlash = Math.max(fullPath.lastIndexOf('/'), fullPath.lastIndexOf('\\'));
    return fullPath.substring(0, lastSlash);
  }
  
  const directory = getFileDirectory(Office.context.document.url);

  const debounce = (fn: (...args: any[]) => void, delay?: number) => {
    let timer: number | null = null
    return function (this: unknown, ...args: any[]) {
      const context = this
      if (timer !== null) clearTimeout(timer)
      timer = window.setTimeout(() => {
        fn.apply(context, args)
      }, delay)
    }
  }

  const _ResizeObserver = window.ResizeObserver
  window.ResizeObserver = class ResizeObserver extends _ResizeObserver {
    constructor(callback: ResizeObserverCallback) {
      callback = debounce(callback, 16)
      super(callback)
    }
  }

  app.use(i18n)
  app.use(router)
  app.mount('#app')
})