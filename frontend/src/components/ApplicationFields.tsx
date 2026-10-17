import { type ReactNode } from "react"

import { ListEditor } from "@/components/ListEditor"
import { SkillChips } from "@/components/SkillChips"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input, Label, Select, Textarea } from "@/components/ui/input"
import type { Application } from "@/lib/api"
import { type MessageKey, useT } from "@/lib/i18n"
import { WORK_MODES, workModeLabel } from "@/lib/status"
import { SALARY_BASES, SALARY_PERIODS } from "@/lib/utils"

function Field({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={className}>
      <Label className="mb-1 block">{label}</Label>
      {children}
    </div>
  )
}

/** Application form, shared by the create and detail pages. */
export function ApplicationFields({ value, set }: {
  value: <K extends keyof Application>(key: K) => Application[K]
  set: <K extends keyof Application>(key: K, v: Application[K]) => void
}) {
  const t = useT()
  const importance = [
    { value: "required", label: t("importance.required") },
    { value: "nice_to_have", label: t("importance.nice_to_have") },
  ]
  const text = (key: keyof Application) => ({
    value: (value(key) as string | null) ?? "",
    onChange: (e: { target: { value: string } }) => set(key, (e.target.value || null) as never),
  })

  return (
    <>
      <Card>
        <CardHeader><CardTitle>{t("application.position")}</CardTitle></CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          <Field label={t("field.title")}><Input {...text("title")} /></Field>
          <Field label={t("field.company")}><Input {...text("company")} /></Field>
          <Field label={t("field.location")}><Input {...text("location")} /></Field>
          <Field label={t("field.workMode")}>
            <Select {...text("work_mode")}>
              <option value="">—</option>
              {WORK_MODES.map((mode) => <option key={mode} value={mode}>{workModeLabel(mode)}</option>)}
            </Select>
          </Field>
          <Field label={t("field.contract")}><Input {...text("contract_type")} /></Field>
          <Field label={t("field.seniority")}><Input {...text("seniority")} /></Field>
          <div className="grid gap-2 sm:col-span-2 sm:grid-cols-[1fr_150px_120px]">
            <Field label={t("field.salary")}>
              <Input {...text("salary")} placeholder={t("field.salaryPlaceholder")} />
            </Field>
            <Field label={t("field.salaryPeriod")}>
              <Select {...text("salary_period")}>
                <option value="">{t("common.notSpecified")}</option>
                {SALARY_PERIODS.map((p) => <option key={p} value={p}>{t(`salaryPeriodOption.${p}`)}</option>)}
              </Select>
            </Field>
            <Field label={t("field.salaryBasis")}>
              <Select {...text("salary_basis")}>
                <option value="">{t("common.notSpecified")}</option>
                {SALARY_BASES.map((b) => <option key={b} value={b}>{t(`salaryBasisOption.${b}`)}</option>)}
              </Select>
            </Field>
          </div>
          <Field label={t("field.experienceYears")}>
            <Input type="number" value={value("experience_years_min") ?? ""}
              onChange={(e) => set("experience_years_min", e.target.value === "" ? null : Number(e.target.value))} />
          </Field>
          <Field label={t("field.education")}><Input {...text("education_required")} /></Field>
          <Field label={t("field.contactName")}><Input {...text("contact_name")} /></Field>
          <Field label={t("field.contactEmail")}><Input {...text("contact_email")} /></Field>
          <Field label={t("field.sourceUrl")} className="sm:col-span-2"><Input {...text("source_url")} /></Field>
          <Field label={t("field.appliedOn")}><Input type="date" {...text("applied_on")} /></Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>{t("application.skills")}</CardTitle></CardHeader>
        <CardContent>
          <SkillChips
            skills={value("skills").map((s) => ({ name: s.name, tag: s.importance }))}
            onChange={(skills) => set("skills", skills.map((s) => ({ name: s.name, importance: s.tag ?? "required" })))}
            tags={importance}
            defaultTag="required"
          />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="grid gap-6 pt-5 md:grid-cols-2">
          {([
            ["requirements", "application.requirements"],
            ["nice_to_have", "application.niceToHave"],
            ["responsibilities", "application.responsibilities"],
            ["benefits", "application.benefits"],
            ["languages", "application.languages"],
          ] as const satisfies readonly [keyof Application, MessageKey][]).map(([key, label]) => (
            <div key={key}>
              <h4 className="mb-2 text-sm font-medium">{t(label)}</h4>
              <ListEditor items={value(key)} onChange={(items) => set(key, items)} />
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>{t("application.notes")}</CardTitle></CardHeader>
        <CardContent>
          <Textarea className="min-h-28" placeholder={t("application.notesPlaceholder")} {...text("notes")} />
        </CardContent>
      </Card>
    </>
  )
}
