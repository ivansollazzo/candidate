import type it from "@/shared/lib/locales/it"

export type MessageKey = keyof typeof it
/** Every locale has exactly the keys of the Italian one: a missing or extra key fails the build. */
export type Messages = Record<MessageKey, string>
