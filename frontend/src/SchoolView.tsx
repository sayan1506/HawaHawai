import React from 'react';
import type {SchoolProfile} from './api';
import type {Resource} from './ui';
import {ResourceStatus} from './ui';
export function SchoolView({resource}: {resource: Resource<SchoolProfile>}) {
  const s = resource.data;
  return <section id="school" className="card" aria-labelledby="school-heading"><p className="eyebrow">ABOUT THIS SCHOOL</p><h2 id="school-heading">School information</h2>
    <ResourceStatus resource={resource} label="school information"/>
    {s && <><h3>{s.name}</h3><dl className="facts"><div><dt>City</dt><dd>{s.city}</dd></div><div><dt>Location</dt><dd>{s.latitude}, {s.longitude}</dd></div>
      <div><dt>Timezone</dt><dd>{s.timezone}</dd></div><div><dt>Supported languages</dt><dd>{s.languages.map(l => l === 'hi' ? 'हिन्दी' : 'English').join(' · ')}</dd></div></dl>
      {s.is_demo && <p className="notice">Fictional demo school in Delhi. This profile does not represent a verified real school.</p>}
      <p>School information is read-only. Profile changes require the existing administrative workflow.</p></>}
  </section>;
}
