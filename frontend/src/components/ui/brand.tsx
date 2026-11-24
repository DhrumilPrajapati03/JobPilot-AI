import {Command} from 'lucide-react';
import {cn} from '../../lib/utils';

export function Brand({compact=false,className}:{compact?:boolean;className?:string}) {
  return <span className={cn('brand',className)}>
    <span className="brand-mark" aria-hidden="true"><Command size={19} strokeWidth={1.8}/></span>
    {!compact&&<span>JobPilot <span className="brand-ai">AI</span></span>}
  </span>;
}
