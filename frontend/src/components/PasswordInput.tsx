import { useState, type InputHTMLAttributes } from 'react'

// A password field with a Show/Hide button, so shoppers can check what they typed.
export default function PasswordInput(props: InputHTMLAttributes<HTMLInputElement> & { id: string }) {
  const [visible, setVisible] = useState(false)
  return (
    <div className="password-field">
      <input {...props} type={visible ? 'text' : 'password'} />
      <button
        type="button"
        className="reveal-btn"
        onClick={() => setVisible((v) => !v)}
        aria-controls={props.id}
        aria-pressed={visible}
      >
        {visible ? 'Hide' : 'Show'}
      </button>
    </div>
  )
}
