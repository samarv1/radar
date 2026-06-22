import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// TODO (SSO): Replace this cookie check with a proper session/JWT validation
// once SSO is introduced. Remove this file and the /login + /api/auth routes.
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname.startsWith("/login") || pathname.startsWith("/api/auth")) {
    return NextResponse.next();
  }

  const auth = request.cookies.get("radar_auth");
  if (!auth || auth.value !== "1") {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
