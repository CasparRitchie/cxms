document.addEventListener('DOMContentLoaded', function () {
  var app = document.getElementById('history-app');
  if (!app) return;

  var STORAGE_KEY = 'gcseHistoryGameV2';
  var game = { xp: 0, streak: 1, lastVisit: '', completed: {}, achievements: [], mythCorrect: 0, daily: {} };
  try { game = Object.assign(game, JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')); } catch (e) {}

  var now = new Date();
  var todayKey = now.toISOString().slice(0, 10);
  if (game.lastVisit !== todayKey) {
    if (game.lastVisit) {
      var days = Math.round((now - new Date(game.lastVisit + 'T00:00:00')) / 86400000);
      game.streak = days === 1 ? (game.streak || 0) + 1 : 1;
    } else game.streak = 1;
    game.lastVisit = todayKey;
  }
  if (!game.daily || game.daily.date !== todayKey) game.daily = { date: todayKey, index: 0, correct: 0, answered: 0, missed: [], complete: false };

  var levels = [
    { name: 'History Rookie', min: 0 }, { name: 'Archive Explorer', min: 250 },
    { name: 'Timeline Detective', min: 600 }, { name: 'Evidence Expert', min: 1100 },
    { name: 'Time Guardian', min: 1800 }
  ];

  var myths = [
    {d:'easy',s:'Kaiser Wilhelm II became German Emperor in 1888.',a:true,e:'Wilhelm II became Kaiser in 1888, the “Year of Three Emperors”.'},
    {d:'easy',s:'All adult German men could vote for the Reichstag before 1914.',a:true,e:'Adult men elected the Reichstag, although the Kaiser still appointed the Chancellor.'},
    {d:'easy',s:'The Reichstag appointed and dismissed the Chancellor.',a:false,e:'The Kaiser appointed and dismissed the Chancellor; the Reichstag could not choose the government.'},
    {d:'easy',s:'The SPD became the largest Reichstag party in 1912.',a:true,e:'The SPD won the most seats in 1912, but it did not control the government.'},
    {d:'easy',s:'The Turnip Winter happened during the First World War.',a:true,e:'Food shortages made the winter of 1916–17 known as the Turnip Winter.'},
    {d:'easy',s:'Kaiser Wilhelm II abdicated in November 1918.',a:true,e:'He abdicated on 9 November 1918 as revolution spread across Germany.'},
    {d:'easy',s:'The Treaty of Versailles was signed in 1919.',a:true,e:'The treaty was signed on 28 June 1919.'},
    {d:'easy',s:'Hyperinflation reached its worst point in 1923.',a:true,e:'The Ruhr crisis and money printing drove catastrophic inflation in 1923.'},
    {d:'easy',s:'Gustav Stresemann introduced the Rentenmark.',a:true,e:'The Rentenmark helped stabilise the currency in 1923.'},
    {d:'easy',s:'Germany joined the League of Nations in 1926.',a:true,e:'Germany joined in 1926 after improving relations under Stresemann.'},
    {d:'medium',s:'Article 48 allowed the President to rule by emergency decree.',a:true,e:'Article 48 gave the President emergency powers, later used increasingly after 1930.'},
    {d:'medium',s:'The Kapp Putsch succeeded and replaced the Weimar government.',a:false,e:'It collapsed after workers organised a general strike.'},
    {d:'medium',s:'The Dawes Plan cancelled German reparations.',a:false,e:'It reorganised payments and brought US loans; reparations continued.'},
    {d:'medium',s:'Nazi support rose continuously between July 1932 and January 1933.',a:false,e:'Nazi seats fell from 230 in July 1932 to 196 in November 1932.'},
    {d:'medium',s:'The Nazis won an outright majority in a free Reichstag election.',a:false,e:'They became the largest party but never won over half the vote in a free Reichstag election.'},
    {d:'medium',s:'Hitler was elected Chancellor directly by the German people.',a:false,e:'President Hindenburg appointed Hitler Chancellor on 30 January 1933.'},
    {d:'medium',s:'Von Papen believed Hitler could be controlled.',a:true,e:'Papen persuaded Hindenburg that conservative ministers could contain Hitler.'},
    {d:'medium',s:'Only three Nazis initially held cabinet posts when Hitler became Chancellor.',a:true,e:'Conservatives thought this limited Nazi presence would make Hitler manageable.'},
    {d:'medium',s:'The Enabling Act allowed Hitler to make laws without the Reichstag.',a:true,e:'Passed on 23 March 1933, it destroyed parliamentary checks on Hitler’s government.'},
    {d:'hard',s:'The Reichstag Fire automatically made Hitler dictator.',a:false,e:'It helped Hitler suspend civil liberties, but dictatorship was created through several steps including the Enabling Act.'},
    {d:'hard',s:'The Night of the Long Knives mainly targeted foreign enemies.',a:false,e:'It targeted Röhm, SA leaders and other domestic political opponents.'},
    {d:'hard',s:'The Gestapo had enough officers to watch every German constantly.',a:false,e:'It had limited staff and relied heavily on public denunciations.'},
    {d:'hard',s:'Nazi unemployment fell only because of autobahn construction.',a:false,e:'Rearmament, conscription, labour controls and exclusions from statistics were also important.'},
    {d:'hard',s:'The Nazis relied only on terror to control Germany.',a:false,e:'Terror mattered, but propaganda, popular support, social pressure and economic recovery also helped sustain control.'},
    {d:'hard',s:'Stresemann permanently solved every weakness of the Weimar Republic.',a:false,e:'Recovery was real but fragile, especially because Germany depended heavily on US loans.'},
    {d:'hard',s:'The Holocaust began immediately when Hitler became Chancellor in January 1933.',a:false,e:'Persecution escalated over years, from discrimination and exclusion to mass murder during the Second World War.'}
  ];

  var missions = [
    { id:'choose-course', title:'Build your course', detail:'Choose your four AQA modules.', xp:50 },
    { id:'open-knowledge', title:'Open the archive', detail:'Explore a detailed Germany knowledge card.', xp:40 },
    { id:'myth-three', title:'Mythbuster rookie', detail:'Answer three Mythbusters correctly.', xp:100 },
    { id:'daily-ten', title:'Daily fact sprint', detail:'Complete today’s 10-question challenge.', xp:150 },
    { id:'submit-answer', title:'Face the examiner', detail:'Submit a practice answer for feedback.', xp:150 },
    { id:'repair-timeline', title:'Repair the timeline', detail:'Trigger and learn from a factual correction.', xp:125 }
  ];

  function save(){ localStorage.setItem(STORAGE_KEY, JSON.stringify(game)); }
  function hashDate(str){ var h=0; for(var i=0;i<str.length;i++) h=(h*31+str.charCodeAt(i))>>>0; return h; }
  function dailySet(){
    var arr=myths.map(function(m,i){return {m:m,i:i};}); var seed=hashDate(todayKey);
    for(var i=arr.length-1;i>0;i--){ seed=(seed*1664525+1013904223)>>>0; var j=seed%(i+1); var t=arr[i];arr[i]=arr[j];arr[j]=t; }
    var missed=(game.daily.missed||[]).map(function(i){return {m:myths[i],i:i};}).filter(function(x){return x.m;});
    var seen={}; return missed.concat(arr).filter(function(x){if(seen[x.i])return false;seen[x.i]=true;return true;}).slice(0,10);
  }
  function levelForXp(){var c=levels[0];levels.forEach(function(l){if(game.xp>=l.min)c=l;});return c;}
  function nextLevel(){for(var i=0;i<levels.length;i++)if(levels[i].min>game.xp)return levels[i];return null;}
  function toast(message){var b=document.createElement('div');b.className='history-game-toast';b.textContent=message;document.body.appendChild(b);requestAnimationFrame(function(){b.classList.add('show');});setTimeout(function(){b.classList.remove('show');setTimeout(function(){b.remove();},300);},2600);}
  function complete(id){if(game.completed[id])return;var m=missions.find(function(x){return x.id===id;});game.completed[id]=true;game.xp+=m?m.xp:25;if(m)toast('Mission complete: '+m.title+' +'+m.xp+' XP');checkAchievements();save();renderHud();renderMissions();}
  function checkAchievements(){[
    {id:'first-steps',when:Object.keys(game.completed).length>=1,label:'First Steps'},
    {id:'mythbuster',when:game.mythCorrect>=3,label:'Mythbuster'},
    {id:'perfect-recall',when:game.daily.complete&&game.daily.correct===10,label:'Perfect Recall'},
    {id:'scholar',when:game.xp>=500,label:'Rising Historian'},
    {id:'streak-three',when:game.streak>=3,label:'3-Day Streak'}
  ].forEach(function(x){if(x.when&&game.achievements.indexOf(x.id)===-1){game.achievements.push(x.id);toast('Achievement unlocked: '+x.label);}});}

  var hud=document.createElement('section');hud.className='history-game-hud';hud.innerHTML='<div><span class="game-label">YOUR HISTORIAN</span><strong id="game-level"></strong></div><div class="game-xp-wrap"><div class="game-xp-track"><span id="game-xp-bar"></span></div><small id="game-xp-copy"></small></div><div class="game-stat"><strong id="game-streak"></strong><span>day streak</span></div><button type="button" id="game-missions-button">View missions</button>';app.insertBefore(hud,app.querySelector('.history-tabs'));
  var missionPanel=document.createElement('section');missionPanel.className='history-game-panel card';missionPanel.hidden=true;hud.insertAdjacentElement('afterend',missionPanel);
  var mythPanel=document.createElement('section');mythPanel.className='mythbuster-card card';mythPanel.innerHTML='<div class="myth-header"><div><span class="game-label">DAILY FACT SPRINT</span><h3>🔥 History Mythbusters</h3></div><strong id="myth-score"></strong></div><div class="myth-progress"><span id="myth-progress-bar"></span></div><div class="myth-meta"><span id="myth-difficulty"></span><span id="myth-count"></span></div><p id="myth-statement" class="myth-statement"></p><div class="myth-actions"><button type="button" data-answer="true">TRUE</button><button type="button" data-answer="false">FALSE</button></div><div id="myth-result" class="myth-result" aria-live="polite"></div>';
  var coursePanel=document.getElementById('course-panel');coursePanel.insertBefore(mythPanel,coursePanel.querySelector('.course-builder'));

  function renderHud(){var l=levelForXp(),n=nextLevel(),start=l.min,end=n?n.min:Math.max(game.xp,start+500);document.getElementById('game-level').textContent=l.name+' · '+game.xp+' XP';document.getElementById('game-streak').textContent='🔥 '+game.streak;document.getElementById('game-xp-bar').style.width=Math.max(0,Math.min(100,((game.xp-start)/(end-start))*100))+'%';document.getElementById('game-xp-copy').textContent=n?(n.min-game.xp)+' XP to '+n.name:'Maximum rank reached';}
  function renderMissions(){missionPanel.innerHTML='<div class="mission-heading"><div><span class="game-label">CAMPAIGN MODE</span><h3>Your missions</h3></div><button type="button" id="close-missions">Close</button></div><div class="mission-grid">'+missions.map(function(m){var done=!!game.completed[m.id];return '<article class="mission '+(done?'done':'')+'"><span>'+(done?'✓':'○')+'</span><div><strong>'+m.title+'</strong><p>'+m.detail+'</p></div><b>+'+m.xp+' XP</b></article>';}).join('')+'</div>';document.getElementById('close-missions').onclick=function(){missionPanel.hidden=true;};}
  function renderMyth(){
    var set=dailySet();
    if(game.daily.complete||game.daily.index>=set.length){
      game.daily.complete=true;save();complete('daily-ten');
      var perfect=game.daily.correct===10;
      document.getElementById('myth-statement').textContent=perfect?'Perfect recall! You repaired every timeline.':'Sprint complete — missed facts will return in a future challenge.';
      document.getElementById('myth-score').textContent=game.daily.correct+'/10';document.getElementById('myth-count').textContent='Complete';document.getElementById('myth-difficulty').textContent=perfect?'🏆 PERFECT':'✅ FINISHED';document.getElementById('myth-progress-bar').style.width='100%';
      mythPanel.querySelector('.myth-actions').hidden=true;document.getElementById('myth-result').innerHTML='<strong>+'+(perfect?200:100)+' XP earned</strong><p>'+(perfect?'Outstanding factual recall.':'Good work. Your weaker facts have been saved for another round.')+'</p>';
      if(!game.daily.rewarded){game.xp+=perfect?200:100;game.daily.rewarded=true;checkAchievements();save();renderHud();}
      return;
    }
    var item=set[game.daily.index],myth=item.m;
    mythPanel.dataset.current=String(item.i);mythPanel.querySelector('.myth-actions').hidden=false;
    document.getElementById('myth-statement').textContent=myth.s;document.getElementById('myth-score').textContent=game.daily.correct+' correct';document.getElementById('myth-count').textContent=(game.daily.index+1)+' of 10';document.getElementById('myth-difficulty').textContent=myth.d.toUpperCase();document.getElementById('myth-difficulty').className='difficulty '+myth.d;document.getElementById('myth-progress-bar').style.width=(game.daily.index*10)+'%';document.getElementById('myth-result').innerHTML='';mythPanel.querySelectorAll('.myth-actions button').forEach(function(b){b.disabled=false;});
  }

  document.getElementById('game-missions-button').onclick=function(){missionPanel.hidden=!missionPanel.hidden;if(!missionPanel.hidden)renderMissions();};
  mythPanel.querySelectorAll('.myth-actions button').forEach(function(button){button.addEventListener('click',function(){var idx=Number(mythPanel.dataset.current),myth=myths[idx],correct=(button.dataset.answer==='true')===myth.a;mythPanel.querySelectorAll('.myth-actions button').forEach(function(b){b.disabled=true;});document.getElementById('myth-result').innerHTML='<strong>'+(correct?'✅ Correct! +25 XP':'🚨 Timeline alert!')+'</strong><p>'+myth.e+'</p><button type="button" id="next-myth">Next fact</button>';game.daily.answered+=1;if(correct){game.daily.correct+=1;game.mythCorrect+=1;game.xp+=25;}else if(game.daily.missed.indexOf(idx)===-1)game.daily.missed.push(idx);if(game.mythCorrect>=3)complete('myth-three');checkAchievements();save();renderHud();document.getElementById('next-myth').onclick=function(){game.daily.index+=1;save();renderMyth();};});});

  document.querySelectorAll('#course-builder input[type="radio"]').forEach(function(i){i.addEventListener('change',function(){complete('choose-course');});});
  document.addEventListener('toggle',function(e){if(e.target.matches('.topic-card details')&&e.target.open)complete('open-knowledge');},true);
  var form=document.getElementById('practice-form');if(form)form.addEventListener('submit',function(){var a=document.getElementById('student-answer');if(a&&a.value.trim())complete('submit-answer');});
  var feedback=document.getElementById('feedback-panel');if(feedback&&window.MutationObserver)new MutationObserver(function(){var t=feedback.textContent.toLowerCase();if(t.indexOf('correction')!==-1||t.indexOf('historical error')!==-1||t.indexOf('timeline alert')!==-1){complete('repair-timeline');feedback.classList.add('timeline-repair-active');}}).observe(feedback,{childList:true,subtree:true});

  renderHud();renderMissions();renderMyth();checkAchievements();save();
});