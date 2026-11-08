import { useEffect } from "react"

/** Sets the browser tab title, e.g. "Agenda · Candidate". */
export function usePageTitle(title: string | null | undefined) {
  useEffect(() => {
    document.title = title ? `${title} · Candidate` : "Candidate"
  }, [title])
}
