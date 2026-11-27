import {cn} from '../../lib/utils';

/** The JobDots mark: two dots (the same mark as the extension's side panel). */
export function Brand({compact=false,className}:{compact?:boolean;className?:string}) {
  return <span className={cn('brand',className)}>
    <span className="jd-mark" aria-hidden="true"><i/><i/></span>
    {!compact&&<span>JobDots</span>}
  </span>;
}
