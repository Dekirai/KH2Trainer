"""Generate an offline diagnostic catalog only from captured source records."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'work/trainer/research'
meta=json.loads((OUT/'managed_tools_round3_metadata.json').read_text(encoding='utf-8'))
table=meta['tables']
languages=[{'Id':i,'Code':code,'Name':name} for i,(code,name) in enumerate([
    ('ja','Japanese'),('en','English'),('fr','French'),('it','Italian'),('de','German'),('es','Spanish')])]
titles=['Corrupt save data','System data creation failed','Save failed','Delete failed',
        'Corrupt data cannot be loaded','Launcher offline: shutdown request','Launcher offline: close request','Launcher login failed']
summaries=[
 'Reports that corrupt save data will be deleted and recreated. The dialog itself does not delete files; that operation belongs to its caller.',
 'Reports a failed attempt to create system data. The first button quits; the second button returns to the caller, whose surrounding workflow can retry.',
 'Reports failure to save game data. The text does not identify the underlying I/O error.',
 'Reports failure to delete game data. The dialog itself does not perform deletion.',
 'Reports corrupt save data that could not be loaded. The same ID is also used from the native save-image decoding error path.',
 'Retains an Epic Games Launcher offline message in this Steam executable. It does not establish that the Epic path is active in a given session.',
 'Has the same original text and buttons as ID 5, but its native post-dialog branch requests a managed window close instead of setting the shutdown field.',
 'Retains an Epic Games Launcher login error. Acknowledging the information dialog leads to the native shutdown request regardless of the dialog boolean result.'
]
effects=[
 ('Acknowledgement returns false. This dispatcher has no additional shutdown action for ID 0.','No second button.'),
 ('The relabeled first button returns true, calls the managed ExitApplication bridge and returns true to the native caller.','The relabeled second button returns false. This dispatcher does not itself retry file creation.'),
 ('Acknowledgement returns false. This dispatcher has no additional shutdown action for ID 2.','No second button.'),
 ('Acknowledgement returns false. This dispatcher has no additional shutdown action for ID 3.','No second button.'),
 ('Acknowledgement returns false. This dispatcher has no additional shutdown action for ID 4; the decoding error caller can still unwind.','No second button.'),
 ('The relabeled first button returns true; the dispatcher writes 256 to AppInterface + 4752 and returns true. MyApp Update subsequently returns exit status 2.','The relabeled Retry button returns false. This dispatcher does not itself reconnect or authenticate.'),
 ('The relabeled first button returns true and calls the managed ExitApplication bridge.','The relabeled Retry button returns false. No retry implementation is present in this dispatcher.'),
 ('The information dialog returns false, but the native ID-7 branch unconditionally writes 256 to AppInterface + 4752 and returns true.','No second button.')
]

def loc(row):
    raw=bytes.fromhex(row['rawHex'])
    ptr=lambda off:hex(int.from_bytes(raw[off:off+8],'little'))
    confirm=row['confirmation']!=0
    return {'LanguageId':row['language'],'Text':row['text'],'PrimaryButton':row['ok'] or 'OK',
      'SecondaryButton':(row['cancel'] or 'Cancel') if confirm else None,
      'TextAddress':row['textPointer'],'PrimaryButtonAddress':ptr(8) if row['ok'] else '0x1405aee00',
      'SecondaryButtonAddress':(ptr(16) if row['cancel'] else '0x1405aee08') if confirm else None,
      'RecordAddress':hex(0x140000000+int(row['rva'],16))}

messages=[]
for index in range(8):
    rows=[r for r in table['Axa._wtable']['entries'] if r['message']==index]
    assert len(rows)==6 and len({r['confirmation'] for r in rows})==1
    messages.append({'Id':index,'Title':titles[index],'Summary':summaries[index],
      'NativeStyle':rows[0]['confirmation'],'PrimaryEffect':effects[index][0],'SecondaryEffect':effects[index][1],
      'Localizations':[loc(r) for r in rows]})

prompts=[]
for status,key,title,behavior,field in [
 (0,'idle','Exit confirmation','Uses the generic exit text when native game status is 0. Unknown status values also retain this text. Returning OK allows the owning close workflow to proceed.', 'Axa.strwText'),
 (1,'gameplay','Exit with unsaved progress','Uses the unsaved-progress warning when native game status is 1. Choosing the relabeled Yes/OK button also starts a separate progress-form thread until EndMessageClose sets the shared completion flag.', 'Axa.strwGamePlayText'),
 (2,'busy','Exit in progress','Uses the exiting-progress text for native game status 2. ShowEndMessageBox still presents it using the same relabeled Yes/No confirmation; it starts no additional progress thread in this state.', 'Axa.strwProcessRunText')]:
    values=[]
    for i,row in enumerate(table[field]['entries']):
        yes,no=table['Axa.strwYesText']['entries'][i],table['Axa.strwNoText']['entries'][i]
        values.append({'LanguageId':i,'Text':row['text'],'PrimaryButton':yes['text'],'SecondaryButton':no['text'],
          'TextAddress':row['va'],'PrimaryButtonAddress':yes['va'],'SecondaryButtonAddress':no['va'],
          'RecordAddress':hex(0x140000000+int(table[field]['rva'],16)+i*8)})
    prompts.append({'Id':key,'NativeGameStatus':status,'Title':title,'Behavior':behavior,'Localizations':values})

data={'Schema':1,'SourceSha256':meta['sourceSha256'],
 'Scope':'Offline reference for one verified executable. Original message text is preserved, including spacing and legacy launcher names. This catalog cannot display game dialogs, modify saves, change language or request shutdown.',
 'SharedNativeBehavior':'Native 0x1401042E0 returns true immediately if AppInterface + 4752 is already nonnegative. Otherwise it may terminate a process named WaitTitleProject.exe, calls the audio-pause wrapper, sets GX + 776, and sends synchronous WM_APP+1 to the game window with an in-process int output pointer. After the dialog it clears pause/suspend and applies the ID-specific branch. These paths are documented, never invoked by this catalog. Retry labels do not establish a retry operation within the dialog dispatcher.',
 'Languages':languages,'Messages':messages,'ClosePrompts':prompts,
 'Evidence':['managed_tools_round3_metadata.json: original FieldRVA 0x7144F0, 8 x 6 records of 32 bytes',
   'managed_tools_round3_evidence.json: CIL 0x1A70, 0x1B00, 0x1BF0, 0x8620, 0x8640',
   'managed_tools_round3_wndproc.json: CIL 0xC370, WM_APP+1 dispatch',
   'managed_tools_round3_native_evidence.json: native 0x1401042E0 and language/status getters',
   'managed_tools_round3_exit_native.json: native MyApp Update 0x14014EB70',
   'managed_tools_round3_edges.json: CLR ExitApplication fixup MethodDef 0x060000AA']}
target=ROOT/'trainer/KH2Trainer/Data/runtime_diagnostics.json'
target.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'{target}: {len(messages)} messages, {len(prompts)} exit prompts, 6 exact original languages')
