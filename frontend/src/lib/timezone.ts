/**
 * Timezone utility for formatting dates with user's preferred timezone.
 */

/** Get user's configured timezone from localStorage, default to Asia/Shanghai */
export function getUserTimezone(): string {
  if (typeof window === "undefined") return "Asia/Shanghai";
  return localStorage.getItem("user_timezone") || "Asia/Shanghai";
}

/** Format a date string or Date object to a localized date/time string */
export function formatDateTime(
  dateInput: string | Date | null | undefined,
  options?: {
    dateOnly?: boolean;
    timeOnly?: boolean;
    relative?: boolean;
  }
): string {
  if (!dateInput) return "";
  
  let date: Date;
  if (typeof dateInput === "string") {
    // If the date string has no timezone info, treat as UTC
    // Backend stores dates in UTC but SQLite may strip timezone markers
    let str = dateInput;
    if (str && !str.endsWith("Z") && !str.includes("+") && !/\d{2}:\d{2}:\d{2}-/.test(str)) {
      str = str.replace(" ", "T");
      if (!str.endsWith("Z")) str += "Z";
    }
    date = new Date(str);
  } else {
    date = dateInput;
  }
  if (isNaN(date.getTime())) return "";
  
  const tz = getUserTimezone();
  
  if (options?.relative) {
    return getRelativeTime(date);
  }
  
  try {
    if (options?.dateOnly) {
      return date.toLocaleDateString("zh-CN", { timeZone: tz });
    }
    if (options?.timeOnly) {
      return date.toLocaleTimeString("zh-CN", { timeZone: tz, hour: "2-digit", minute: "2-digit" });
    }
    return date.toLocaleString("zh-CN", {
      timeZone: tz,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    // Fallback if timezone is invalid
    return date.toLocaleString("zh-CN");
  }
}

/** Format a date to a short date string (MM/DD) */
export function formatDateShort(dateInput: string | Date | null | undefined): string {
  if (!dateInput) return "";
  const date = typeof dateInput === "string" ? new Date(dateInput) : dateInput;
  if (isNaN(date.getTime())) return "";
  
  const tz = getUserTimezone();
  try {
    return date.toLocaleDateString("zh-CN", { timeZone: tz, month: "2-digit", day: "2-digit" });
  } catch {
    return date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
  }
}

/** Get relative time description (e.g., "3分钟前") */
function getRelativeTime(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffSec < 60) return "刚刚";
  if (diffMin < 60) return `${diffMin}分钟前`;
  if (diffHour < 24) return `${diffHour}小时前`;
  if (diffDay < 30) return `${diffDay}天前`;
  
  return formatDateTime(date, { dateOnly: true });
}

/** Initialize timezone from user profile on login */
export function initTimezone(timezone: string) {
  if (typeof window !== "undefined") {
    localStorage.setItem("user_timezone", timezone);
  }
}
