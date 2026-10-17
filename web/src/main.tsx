import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import { SkillGateRoot } from "@/root"
import "./index.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <SkillGateRoot />
  </StrictMode>
)
