import type { ReactNode } from "react"

import { Logo } from "@/components/Logo"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { useHealth } from "@/lib/ai"
import { useT } from "@/lib/i18n"

const TECHNOLOGIES = [
  "FastAPI, SQLModel, Alembic, PostgreSQL",
  "React, TypeScript, Vite, Tailwind CSS, TanStack Query, Lucide",
  "Ollama, Ministral 3 3B Instruct, sentence-transformers (multilingual-e5-small)",
  "pdfplumber, python-docx, trafilatura",
  "pwdlib (Argon2), PyJWT, Pillow",
  "Docker Compose",
]

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 px-3 py-2 sm:grid-cols-[10rem_1fr] sm:gap-4">
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

/** Release, author and credits. */
export function InfoTab() {
  const t = useT()
  const { data: health } = useHealth()
  return (
    <Card>
      <CardHeader><Logo className="h-7" /></CardHeader>
      <CardContent className="text-sm">
        <dl className="divide-y rounded-lg border">
          <Row label={t("info.version")}><span className="font-mono">{health?.version ?? "—"}</span></Row>
          <Row label={t("info.build")}><span className="font-mono">{health?.build ?? "—"}</span></Row>
          <Row label={t("info.author")}>Ivan Sollazzo</Row>
          <Row label={t("info.technologies")}>
            <ul className="space-y-0.5">{TECHNOLOGIES.map((line) => <li key={line}>{line}</li>)}</ul>
          </Row>
          <Row label={t("info.thanks")}>{t("info.thanksText")}</Row>
        </dl>
      </CardContent>
    </Card>
  )
}
