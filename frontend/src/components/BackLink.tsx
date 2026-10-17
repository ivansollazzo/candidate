import { ArrowLeft } from "lucide-react"
import { Link } from "react-router"

import { useT } from "@/lib/i18n"

/** Link back to the applications list. */
export function BackLink() {
  const t = useT()
  return (
    <Link to="/applications" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="size-4" /> {t("nav.applications")}
    </Link>
  )
}
