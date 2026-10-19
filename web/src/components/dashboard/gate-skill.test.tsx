import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"

import { GateSkillLine } from "@/components/dashboard/gate-page"
import pageSource from "@/components/dashboard/gate-page.tsx?raw"

describe("Gate tab skill", () => {
  it("keeps the selected skill name on the Gate tab", () => {
    const html = renderToStaticMarkup(<GateSkillLine name="json-response" />)
    expect(html).toContain('id="gate-skill"')
    expect(html).toContain("json-response")
    expect(pageSource).toContain("<GateSkillLine")
  })
})
