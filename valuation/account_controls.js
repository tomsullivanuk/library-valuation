'use strict';
// Carry the current owner page through the family view without changing identity.
for(const link of document.querySelectorAll('[data-family-view]')){
  link.addEventListener('click',()=>{
    const back=location.pathname+location.hash;
    link.href='/browse?owner_return='+encodeURIComponent(back);
  });
}
for(const link of document.querySelectorAll('[data-sign-out]')){
  link.addEventListener('click',()=>{
    const back=location.pathname.startsWith('/owner')?location.pathname+location.hash:new URLSearchParams(location.search).get('owner_return');
    if(back)link.href='/sign-out?owner_return='+encodeURIComponent(back);
  });
}
