import { NextResponse } from "next/server";

// TODO (SSO): Remove this route once SSO is introduced.
export async function POST(request: Request) {
  const { password } = await request.json();

  if (!process.env.SITE_PASSWORD || password !== process.env.SITE_PASSWORD) {
    return NextResponse.json({ error: "Incorrect password" }, { status: 401 });
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set("radar_auth", "1", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    maxAge: 60 * 60 * 24 * 30, // 30 days
    path: "/",
  });
  return res;
}
