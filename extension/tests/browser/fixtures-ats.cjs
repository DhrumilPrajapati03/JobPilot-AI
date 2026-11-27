// Whole application forms in the shape of each provider, authored locally (not copied employer
// pages), for the Applicant path: read the questions, fill, attach the resume, never submit.
const {shell} = require('./fixtures.cjs');
const submitCounter = `<script>window.submits=0;document.querySelector('form').onsubmit=e=>{e.preventDefault();window.submits++;};</script>`;

// Greenhouse: separate first/last name, native select, required resume upload, consent box.
const greenhouse = shell(`<form id="application_form">
<div class="field"><label for="first_name">First Name *</label><input id="first_name" name="first_name" required></div>
<div class="field"><label for="last_name">Last Name *</label><input id="last_name" name="last_name" required></div>
<div class="field"><label for="email">Email *</label><input id="email" type="email" name="email" required></div>
<div class="field"><label for="phone">Phone</label><input id="phone" type="tel" name="phone"></div>
<div class="field"><label for="resume">Resume/CV *</label><input id="resume" type="file" accept=".pdf,.doc,.docx" required></div>
<div class="field"><label for="linkedin">LinkedIn Profile</label><input id="linkedin" type="url"></div>
<div class="field"><label for="notice">Notice period</label><select id="notice"><option value="">Select...</option><option>Immediately</option><option>30 days</option><option>60 days</option></select></div>
<div class="field"><label><input id="consent" type="checkbox" required> I agree to the privacy policy</label></div>
<button type="submit">Submit Application</button></form>${submitCounter}`);

// Lever: one "Full name", resume first, URLs block, a radio group for work authorisation.
const lever = shell(`<form id="lever-application">
<div class="application-question"><label for="resume-upload">Resume/CV ✱</label><input id="resume-upload" type="file" name="resume" required></div>
<div class="application-question"><label for="name">Full name ✱</label><input id="name" name="name" required></div>
<div class="application-question"><label for="lev-email">Email ✱</label><input id="lev-email" type="email" name="email" required></div>
<div class="application-question"><label for="lev-phone">Phone</label><input id="lev-phone" type="tel" name="phone"></div>
<div class="application-question"><label for="org">Current company</label><input id="org" name="org"></div>
<div class="application-question"><label for="lev-li">LinkedIn URL</label><input id="lev-li" type="url" name="urls[LinkedIn]"></div>
<fieldset><legend>Are you legally authorized to work in India? ✱</legend>
<label><input type="radio" name="auth" value="Yes" required>Yes</label><label><input type="radio" name="auth" value="No">No</label></fieldset>
<div class="application-question"><label for="comments">Additional information</label><textarea id="comments" name="comments"></textarea></div>
<button type="submit">Submit application</button></form>${submitCounter}`);

// Ashby: labels by id, the file input hidden behind a visible upload button, a searchable
// location combobox with a linked listbox, and a cover letter upload that is not the resume.
const ashby = shell(`<form id="ashby-form">
<div><label for="_systemfield_name">Name *</label><input id="_systemfield_name" required></div>
<div><label for="_systemfield_email">Email *</label><input id="_systemfield_email" type="email" required></div>
<div><label id="resume-label">Resume *</label><div class="dropzone"><button type="button">Upload File</button>
<input id="_systemfield_resume" type="file" aria-labelledby="resume-label" style="display:none" required></div></div>
<div><label id="cover-label">Cover letter</label><div class="dropzone"><button type="button">Upload File</button>
<input id="cover" type="file" aria-labelledby="cover-label" style="display:none"></div></div>
<div><label for="loc">Location</label><input id="loc" role="combobox" aria-controls="loc-list" aria-expanded="false" autocomplete="off">
<div id="loc-list" role="listbox" hidden><div role="option">Pune, Maharashtra, India</div><div role="option">Pune, Indiana, United States</div></div></div>
<button type="submit">Submit Application</button></form>
<script>loc.onclick=()=>{document.getElementById('loc-list').hidden=false;loc.setAttribute('aria-expanded','true')};
loc.oninput=()=>{document.getElementById('loc-list').hidden=false;loc.setAttribute('aria-expanded','true')};
document.getElementById('loc-list').onclick=e=>{if(e.target.getAttribute('role')==='option'){loc.value=e.target.textContent;loc.setAttribute('aria-expanded','false');document.getElementById('loc-list').hidden=true;}};</script>${submitCounter}`);

module.exports = {greenhouse, lever, ashby};
