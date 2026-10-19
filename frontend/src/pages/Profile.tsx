import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ExternalLink, FileUp, Loader2 } from "lucide-react"
import { type ReactNode, useState } from "react"

import { AiAssist } from "@/components/AiAssist"
import { EntryList, type FieldDef } from "@/components/EntryList"
import { ErrorText } from "@/components/ErrorText"
import { ProfilePhoto } from "@/components/ProfilePhoto"
import { SaveBar } from "@/components/SaveBar"
import { SkillsEditor } from "@/components/SkillsEditor"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input, Label, Textarea } from "@/components/ui/input"
import {
  api,
  type Certification,
  type Education,
  type Experience,
  type Language,
  type Profile,
  type ProfileLink,
  type ProfileSkill,
  type Project,
} from "@/lib/api"
import { useAiFill, useAiStatus } from "@/lib/ai"
import { t, useT } from "@/lib/i18n"
import { usePageTitle } from "@/lib/title"
import { formatDate, formatMonth, formatPeriod } from "@/lib/utils"

// Functions, not constants, so labels follow the current language
const experienceFields = (): FieldDef[] => [
  { key: "role", label: t("profile.role") },
  { key: "company", label: t("field.company") },
  { key: "location", label: t("field.location") },
  { key: "employment_type", label: t("profile.employmentType") },
  { key: "start", label: t("profile.start"), type: "date" },
  { key: "end", label: t("profile.end"), type: "date" },
  { key: "current", label: t("profile.current"), type: "checkbox" },
  { key: "technologies", label: t("profile.technologies"), type: "list", wide: true },
  { key: "description", label: t("profile.description"), type: "textarea" },
]

const educationFields = (): FieldDef[] => [
  { key: "degree", label: t("profile.degree") },
  { key: "field_of_study", label: t("profile.fieldOfStudy") },
  { key: "institution", label: t("profile.institution") },
  { key: "location", label: t("field.location") },
  { key: "start", label: t("profile.start"), type: "date" },
  { key: "end", label: t("profile.end"), type: "date" },
  { key: "grade", label: t("profile.grade") },
  { key: "thesis", label: t("profile.thesis") },
  { key: "details", label: t("profile.educationDetails"), type: "textarea" },
]

const projectFields = (): FieldDef[] => [
  { key: "name", label: t("profile.name"), wide: true },
  { key: "context", label: t("profile.context"), placeholder: t("profile.contextPlaceholder") },
  { key: "team", label: t("profile.team"), placeholder: t("profile.teamPlaceholder") },
  { key: "start", label: t("profile.start"), type: "date" },
  { key: "end", label: t("profile.end"), type: "date" },
  { key: "technologies", label: t("profile.technologies"), type: "list", wide: true },
  { key: "description", label: t("profile.description"), type: "textarea" },
]

const certificationFields = (): FieldDef[] => [
  { key: "name", label: t("profile.name"), wide: true },
  { key: "issuer", label: t("profile.issuer") },
  { key: "credential_id", label: t("profile.credentialId") },
  { key: "issued_on", label: t("profile.issuedOn"), type: "date" },
  { key: "expires_on", label: t("profile.expiresOn"), type: "date" },
  { key: "url", label: t("profile.verifyUrl"), wide: true },
]

const languageFields = (): FieldDef[] => [
  { key: "language", label: t("profile.language") },
  { key: "level", label: t("profile.level"), placeholder: t("profile.levelPlaceholder") },
]

const linkFields = (): FieldDef[] => [
  { key: "label", label: t("profile.linkName"), placeholder: "LinkedIn, GitHub, Portfolio" },
  { key: "url", label: t("profile.linkUrl") },
]

function Technologies({ items }: { items: string[] | undefined }) {
  if (!items?.length) return null
  return (
    <div className="mt-1.5 flex flex-wrap gap-1">
      {items.map((tech) => <span key={tech} className="rounded bg-secondary px-1.5 py-0.5 text-xs">{tech}</span>)}
    </div>
  )
}

function Muted({ children }: { children: ReactNode }) {
  return <p className="text-muted-foreground">{children}</p>
}

function Section({ title, children, className }: { title: string; children: ReactNode; className?: string }) {
  return (
    <Card className={className}>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

export function ProfilePage() {
  useT()
  usePageTitle(t("profile.title"))
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<Partial<Profile>>({})
  const { data: profile, error } = useQuery({ queryKey: ["profile"], queryFn: api.getProfile })
  const onSaved = (data: Profile) => {
    queryClient.setQueryData(["profile"], data)
    queryClient.invalidateQueries({ queryKey: ["match"] })
  }
  // Upload only stores the file; fields are filled by hand or with AI
  const upload = useMutation({ mutationFn: api.uploadCv, onSuccess: (data) => queryClient.setQueryData(["profile"], data) })
  const save = useMutation({
    mutationFn: (changes: Partial<Profile>) => api.updateProfile(changes),
    onSuccess: (data) => { setDraft({}); onSaved(data) },
  })
  const ai = useAiStatus()
  const fill = useAiFill<Partial<Profile>>({ ...profile, ...draft }, (changes) => setDraft((d) => ({ ...d, ...changes })))

  if (error) return <ErrorText error={error} />
  if (!profile) return <p className="text-sm text-muted-foreground">{t("common.loading")}</p>

  const value = <K extends keyof Profile>(key: K): Profile[K] => (key in draft ? draft[key] : profile[key]) as Profile[K]
  const set = <K extends keyof Profile>(key: K, v: Profile[K]) => setDraft((d) => ({ ...d, [key]: v }))
  const text = (key: keyof Profile) => ({
    value: (value(key) as string | null) ?? "",
    onChange: (e: { target: { value: string } }) => set(key, (e.target.value || null) as never),
  })

  // Propagate skill removals/renames to projects and experience, or saving would bring the old skill back
  const replaceSkill = (name: string, replacement: ProfileSkill | null) => {
    const key = name.trim().toLowerCase()
    const swap = (techs: string[] = []) => techs.flatMap((tech) =>
      tech.trim().toLowerCase() !== key ? [tech] : replacement ? [replacement.name] : [])
    setDraft((d) => ({
      ...d,
      skills: value("skills").flatMap((s) => (s.name !== name ? [s] : replacement ? [replacement] : [])),
      projects: value("projects").map((p) => ({ ...p, technologies: swap(p.technologies) })),
      experiences: value("experiences").map((e) => ({ ...e, technologies: swap(e.technologies) })),
    }))
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5 pb-20">
      <div>
        <h1 className="text-xl font-semibold">{t("profile.title")}</h1>
        <p className="text-sm text-muted-foreground">
          {ai.enabled ? t("profile.introAi") : t("profile.intro")}
        </p>
      </div>

      <Section title={t("profile.cv")}>
        <div className="flex flex-wrap items-center gap-3">
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-sm hover:bg-accent">
            {upload.isPending ? <Loader2 className="size-4 animate-spin" /> : <FileUp className="size-4" />}
            {profile.cv_filename ? t("profile.uploadNew") : t("profile.upload")}
            <input type="file" className="hidden" accept=".pdf,.docx,.txt,.md" disabled={upload.isPending || fill.running}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) upload.mutate(f)
                e.target.value = ""
              }} />
          </label>
          {profile.cv_filename && <a href="/api/profile/cv" className="text-sm underline">{profile.cv_filename}</a>}
          <span className="ml-auto text-xs text-muted-foreground">{t("profile.updated", { date: formatDate(profile.updated_at) ?? "" })}</span>
        </div>
        <ErrorText className="mt-2" error={upload.error} />
      </Section>

      <AiAssist hint={profile.cv_filename ? t("profile.aiHint") : t("profile.aiHintNoCv")}
        running={fill.running} error={fill.error} canRun={!!profile.cv_filename && !upload.isPending}
        onRun={() => fill.run(api.fillFromCv)} />

      <div className="grid gap-5 lg:grid-cols-[3fr_2fr]">
        <Section title={t("profile.main")}>
          <div className="mb-4 border-b pb-4"><ProfilePhoto /></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div><Label>{t("profile.fullName")}</Label><Input {...text("full_name")} /></div>
            <div><Label>{t("profile.headline")}</Label><Input {...text("headline")} /></div>
            <div><Label>{t("profile.email")}</Label><Input {...text("email")} /></div>
            <div><Label>{t("profile.phone")}</Label><Input {...text("phone")} /></div>
            <div><Label>{t("profile.city")}</Label><Input {...text("location")} /></div>
            <div>
              <Label>{t("profile.years")}</Label>
              <Input type="number" step="0.5" value={value("years_of_experience") ?? ""}
                onChange={(e) => set("years_of_experience", e.target.value === "" ? null : Number(e.target.value))} />
            </div>
            <div className="sm:col-span-2"><Label>{t("profile.summary")}</Label><Textarea {...text("summary")} /></div>
          </div>
        </Section>

        <div className="space-y-5">
          <Section title={t("profile.links")}>
            <EntryList<ProfileLink>
              items={value("links")} onChange={(v) => set("links", v)} fields={linkFields()}
              blank={{ label: "", url: "" }} empty={t("profile.noLinks")} addLabel={t("profile.addLink")}
              render={(l) => (
                <a href={l.url.startsWith("http") ? l.url : `https://${l.url}`} target="_blank" rel="noreferrer"
                  className="inline-flex items-center gap-1 hover:underline">
                  <span className="font-medium">{l.label || l.url}</span><ExternalLink className="size-3" />
                </a>
              )} />
          </Section>
          <Section title={t("profile.languages")}>
            <EntryList<Language>
              items={value("languages")} onChange={(v) => set("languages", v)} fields={languageFields()}
              blank={{ language: "", level: null }} empty={t("profile.noLanguages")} addLabel={t("profile.addLanguage")}
              render={(l) => <p><span className="font-medium">{l.language}</span>{l.level && <span className="text-muted-foreground"> · {l.level}</span>}</p>} />
          </Section>
        </div>
      </div>

      <Section title={t("profile.skills")}>
        <SkillsEditor skills={value("skills")} onChange={(v) => set("skills", v)}
          onRemove={(name) => replaceSkill(name, null)} onRename={replaceSkill} />
      </Section>

      <Section title={t("profile.experiences")}>
        <EntryList<Experience>
          items={value("experiences")} onChange={(v) => set("experiences", v)} fields={experienceFields()}
          blank={{ role: "", company: "", current: false }} empty={t("profile.noExperiences")} addLabel={t("profile.addExperience")}
          render={(e) => (
            <>
              <p className="font-medium">{e.role || t("profile.role")}{e.company && <span className="font-normal text-muted-foreground"> · {e.company}</span>}</p>
              <p className="text-xs text-muted-foreground">
                {[formatPeriod(e.start, e.end, e.current), e.location, e.employment_type].filter(Boolean).join(" · ")}
              </p>
              {e.description && <Muted>{e.description}</Muted>}
              <Technologies items={e.technologies} />
            </>
          )} />
      </Section>

      <Section title={t("profile.education")}>
        <EntryList<Education>
          items={value("education")} onChange={(v) => set("education", v)} fields={educationFields()}
          blank={{ degree: "", institution: "" }} empty={t("profile.noEducation")} addLabel={t("profile.addEducation")}
          render={(e) => (
            <>
              <p className="font-medium">{[e.degree, e.field_of_study].filter(Boolean).join(" – ") || t("profile.degree")}</p>
              <p className="text-xs text-muted-foreground">
                {[e.institution, formatPeriod(e.start, e.end), e.grade && t("profile.gradeValue", { grade: e.grade })].filter(Boolean).join(" · ")}
              </p>
              {e.thesis && <Muted>{t("profile.thesisValue", { thesis: e.thesis })}</Muted>}
              {e.details && <Muted>{e.details}</Muted>}
            </>
          )} />
      </Section>

      <Section title={t("profile.projects")}>
        <EntryList<Project>
          items={value("projects")} onChange={(v) => set("projects", v)} fields={projectFields()}
          blank={{ name: "", technologies: [] }} empty={t("profile.noProjects")} addLabel={t("profile.addProject")}
          render={(p) => (
            <>
              <p className="font-medium">{p.name || t("profile.project")}</p>
              <p className="text-xs text-muted-foreground">
                {[formatPeriod(p.start, p.end), p.context, p.team].filter(Boolean).join(" · ")}
              </p>
              {p.description && <Muted>{p.description}</Muted>}
              <Technologies items={p.technologies} />
            </>
          )} />
      </Section>

      <Section title={t("profile.certifications")}>
        <EntryList<Certification>
          items={value("certifications")} onChange={(v) => set("certifications", v)} fields={certificationFields()}
          blank={{ name: "" }} empty={t("profile.noCertifications")} addLabel={t("profile.addCertification")}
          render={(c) => (
            <>
              <p className="font-medium">{c.name || t("profile.certification")}</p>
              <p className="text-xs text-muted-foreground">
                {[c.issuer, c.issued_on && t("profile.issuedValue", { date: formatMonth(c.issued_on) ?? "" }),
                  c.expires_on && t("profile.expiresValue", { date: formatMonth(c.expires_on) ?? "" })]
                  .filter(Boolean).join(" · ")}
              </p>
              {c.url && <a href={c.url} target="_blank" rel="noreferrer" className="text-xs underline">{t("profile.verify")}</a>}
            </>
          )} />
      </Section>

      {Object.keys(draft).length > 0 && (
        <SaveBar message={t("common.unsaved")} saving={save.isPending} error={save.error?.message}
          onCancel={() => setDraft({})} onSave={() => save.mutate(draft)} />
      )}
    </div>
  )
}
