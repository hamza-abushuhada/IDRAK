import { NextResponse, type NextRequest } from "next/server";

const LOCALES = ["ar", "en"];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const first = pathname.split("/")[1];
  if (LOCALES.includes(first)) return NextResponse.next();
  const saved = req.cookies.get("basira_locale")?.value;
  const accept = req.headers.get("accept-language") || "";
  const locale = saved && LOCALES.includes(saved) ? saved : accept.toLowerCase().startsWith("en") ? "en" : "ar";
  const url = req.nextUrl.clone();
  url.pathname = `/${locale}${pathname === "/" ? "" : pathname}`;
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!_next|api|favicon.ico|brand|images|samples|.*\\.[a-zA-Z0-9]+$).*)"],
};
