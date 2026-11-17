(()=>{
 const shell=document.querySelector('.app-shell');
 if(!shell)return;
 const workspace=shell.dataset.workspace||'default';
 const toggle=document.getElementById('sidebar-toggle');
 const mobile=()=>window.matchMedia('(max-width:760px)').matches;
 const setSidebar=()=>{
  const open=mobile()?shell.classList.contains('sidebar-open'):!shell.classList.contains('sidebar-collapsed');
  if(toggle){toggle.textContent=mobile()?(open?'×':'☰'):(open?'‹':'›');toggle.setAttribute('aria-label',open?'Minimize sidebar':'Expand sidebar');toggle.title=open?'Minimize sidebar':'Expand sidebar'}
 };
 const collapsedKey='forma-collapsed-tree:'+workspace;
 let collapsed=new Set();
 try{collapsed=new Set(JSON.parse(localStorage.getItem(collapsedKey)||'[]'))}catch{}
 const rows=[...shell.querySelectorAll('.nav-row')];
 rows.forEach(row=>{const button=row.querySelector('[data-tree-toggle]');if(button&&collapsed.has(row.querySelector('.nav-item')?.getAttribute('href'))){button.setAttribute('aria-expanded','false');button.textContent='›'}});
 const updateTree=()=>{
  const collapsedLevels=[];
  rows.forEach(row=>{
   const level=Number(row.dataset.depth||0);while(collapsedLevels.length&&collapsedLevels.at(-1)>=level)collapsedLevels.pop();
   row.hidden=collapsedLevels.length>0;
   const button=row.querySelector('[data-tree-toggle]');if(button&&button.getAttribute('aria-expanded')==='false')collapsedLevels.push(level);
  });
 };
 rows.forEach(row=>{const button=row.querySelector('[data-tree-toggle]');if(!button)return;button.addEventListener('click',()=>{
   const open=button.getAttribute('aria-expanded')!=='false';button.setAttribute('aria-expanded',String(!open));button.textContent=open?'›':'⌄';button.setAttribute('aria-label',`${open?'Expand':'Collapse'} ${row.querySelector('.nav-title')?.textContent||'page'}`);
   const link=row.querySelector('.nav-item')?.getAttribute('href');if(link){if(open)collapsed.add(link);else collapsed.delete(link);localStorage.setItem(collapsedKey,JSON.stringify([...collapsed]))}updateTree();
  })});
 updateTree();setSidebar();
 toggle?.addEventListener('click',()=>{if(mobile()){shell.classList.toggle('sidebar-open')}else{shell.classList.toggle('sidebar-collapsed');localStorage.setItem('forma-sidebar-collapsed',shell.classList.contains('sidebar-collapsed')?'1':'0')}setSidebar()});
 if(!mobile()&&localStorage.getItem('forma-sidebar-collapsed')==='1')shell.classList.add('sidebar-collapsed');setSidebar();
 window.addEventListener('resize',setSidebar);
})();
