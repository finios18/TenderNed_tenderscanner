import Link from "next/link";
import { Radar } from "lucide-react";
export function Brand() {
  return <Link className="brand" href="/" aria-label="Tenderprofiel — naar de homepage"><span className="brand-mark"><Radar size={23} strokeWidth={1.8}/></span>Tenderprofiel<span className="poc-tag">pilot</span></Link>;
}
