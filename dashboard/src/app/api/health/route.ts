import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    status: "ok",
    service: "ForgeAI Dashboard",
    timestamp: Date.now() / 1000,
  });
}
