import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'

const isMainView = new URLSearchParams(window.location.search).get("view") === "main"
const Page = isMainView
  ? lazy(() => import("./DesktopApp.tsx"))
  : lazy(() => import("./App.tsx"))

document.title = isMainView ? "曹操传随机工具" : "结果统计"

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Suspense fallback={<div className="grid min-h-screen place-items-center text-sm text-muted-foreground">正在加载</div>}>
      <Page />
    </Suspense>
  </StrictMode>,
)
