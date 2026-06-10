import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import { Bold, Italic, List, ImageIcon } from 'lucide-react'

interface Props {
  content: string
  onChange: (html: string) => void
  readOnly?: boolean
}

export function RationaleEditor({ content, onChange, readOnly = false }: Props) {
  const editor = useEditor({
    extensions: [
      StarterKit,
      Image.configure({ inline: false, allowBase64: true }),
    ],
    content,
    editable: !readOnly,
    onUpdate: ({ editor }) => onChange(editor.getHTML()),
  })

  const handleImagePaste = () => {
    if (!editor) return
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*'
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (!file) return
      const reader = new FileReader()
      reader.onload = (ev) => {
        const src = ev.target?.result as string
        editor.chain().focus().setImage({ src }).run()
      }
      reader.readAsDataURL(file)
    }
    input.click()
  }

  return (
    <div style={styles.wrapper}>
      {!readOnly && (
        <div style={styles.toolbar}>
          <button style={styles.toolBtn} onMouseDown={e => { e.preventDefault(); editor?.chain().focus().toggleBold().run() }}>
            <Bold size={14} />
          </button>
          <button style={styles.toolBtn} onMouseDown={e => { e.preventDefault(); editor?.chain().focus().toggleItalic().run() }}>
            <Italic size={14} />
          </button>
          <button style={styles.toolBtn} onMouseDown={e => { e.preventDefault(); editor?.chain().focus().toggleBulletList().run() }}>
            <List size={14} />
          </button>
          <button style={styles.toolBtn} onMouseDown={e => { e.preventDefault(); handleImagePaste() }}>
            <ImageIcon size={14} />
          </button>
        </div>
      )}
      <EditorContent editor={editor} style={styles.editor} />
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  wrapper: { border: '1px solid #e5e7eb', borderRadius: 6, overflow: 'hidden', background: '#fff' },
  toolbar: { display: 'flex', gap: 4, padding: '6px 8px', borderBottom: '1px solid #e5e7eb', background: '#f9fafb' },
  toolBtn: { border: '1px solid #e5e7eb', background: '#fff', borderRadius: 4, padding: '3px 7px', cursor: 'pointer', display: 'flex', alignItems: 'center' },
  editor: { padding: '8px 12px', minHeight: 120, fontSize: 14, lineHeight: 1.6 },
}
