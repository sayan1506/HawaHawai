import type {Forecast,ForecastPoint} from './contracts';

const HOUR=3600000;
// Match the backend requirement for one unambiguous US AQI per hour.
export function forecastAqi(point:ForecastPoint):number|null {
  const values=point.aqi.filter(a=>a.scale==='US_AQI');
  return values.length===1&&Number.isFinite(values[0].value)&&values[0].value>=0?values[0].value:null;
}
// Require an explicit offset and a real calendar date. Date.parse alone accepts
// some impossible dates and local timestamps; identity is always the UTC hour.
export function forecastHour(value:unknown):number|null {
  if(typeof value!=='string')return null;
  const match=/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})$/.exec(value);
  if(!match)return null;
  const [,y,m,d,h,min,sec,fraction]=match;
  const calendar=new Date(Date.UTC(+y,+m-1,+d));
  if(calendar.getUTCFullYear()!==+y||calendar.getUTCMonth()!==+m-1||calendar.getUTCDate()!==+d||+h>23||+min>59||+sec>59||fraction&&/[1-9]/.test(fraction))return null;
  const time=Date.parse(value);
  return Number.isFinite(time)&&time%HOUR===0?time:null;
}

export function forecastCoverage(value:Forecast,now:number) {
  const hours=value.points.map(p=>forecastHour(p.valid_at));
  const start=forecastHour(value.forecast_start),end=forecastHour(value.forecast_end);
  const retrieved=Date.parse(value.retrieved_at||'');
  const complete=value.horizon_hours===48&&hours.length===48&&start!==null&&end!==null&&Number.isFinite(retrieved)&&Number.isFinite(now)
    // Accept the current hour for a response crossing an hour boundary in transit,
    // but never a wholly elapsed hour from an older cached response.
    &&start>=Math.max(Math.ceil(retrieved/HOUR),Math.floor(now/HOUR))*HOUR&&start<=Math.ceil(now/HOUR)*HOUR
    &&end-start===47*HOUR&&hours.every((hour,index)=>hour!==null&&hour===start+index*HOUR);
  return {complete};
}
