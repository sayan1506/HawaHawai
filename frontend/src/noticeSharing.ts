export type ShareNotice={title:string;text:string;validUntil:string};
export const whatsappLink=(notice:ShareNotice)=>'https://wa.me/?text='+encodeURIComponent(notice.text);
export async function nativeShare(notice:ShareNotice,api:{share?:(data:{title:string;text:string})=>Promise<void>;canShare?:(data:{title:string;text:string})=>boolean}) {
  const data={title:notice.title,text:notice.text};
  try {
    if(!api.share||(api.canShare&&!api.canShare(data)))return 'unsupported';
    await api.share(data);return 'shared';
  } catch(error){return (error as {name?:string})?.name==='AbortError'?'canceled':'failed';}
}
export async function copyNotice(notice:ShareNotice,clipboard?:{writeText:(text:string)=>Promise<void>}) {
  try {if(!clipboard)return false;await clipboard.writeText(notice.text);return true;}catch{return false;}
}
