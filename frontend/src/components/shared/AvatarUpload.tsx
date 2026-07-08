import { useRef, useState } from 'react'
import { Camera, Loader2 } from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import { uploadAvatarFile, updateMyAvatar, AvatarUploadError, isDisplayableImageUrl } from '@/lib/api/avatar'

interface AvatarUploadProps {
  initials: string
  size?: 'md' | 'lg'
  shape?: 'circle' | 'square'
  style?: React.CSSProperties
}

/** Self-service profile picture upload, reused across Student/Faculty/Dean/Admin
 * "My Profile" pages. Always targets the signed-in user's own avatar — the
 * backend only allows PATCH /auth/me/avatar for the caller. */
export function AvatarUpload({ initials, size = 'lg', shape = 'circle', style }: AvatarUploadProps) {
  const { user, refreshUser } = useAuth()
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)

  const dimension = size === 'lg' ? 'w-16 h-16' : 'w-10 h-10'
  const roundedCls = shape === 'circle' ? 'rounded-full' : 'rounded-2xl'

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file || !user) return
    setUploading(true)
    try {
      const url = await uploadAvatarFile(user.id, file)
      await updateMyAvatar(url)
      await refreshUser()
      addToast('Profile picture updated.', 'success')
    } catch (err) {
      addToast(err instanceof AvatarUploadError ? err.message : getErrorMessage(err), 'error')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className={`relative ${dimension} flex-shrink-0`}>
      {isDisplayableImageUrl(user?.avatarUrl) ? (
        <img
          src={user!.avatarUrl!}
          alt={user?.fullName ?? ''}
          className={`${dimension} ${roundedCls} object-cover`}
        />
      ) : (
        <div
          className={`${dimension} ${roundedCls} flex items-center justify-center text-xl font-bold`}
          style={style}
        >
          {initials}
        </div>
      )}
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={uploading}
        className="absolute -bottom-1 -right-1 h-6 w-6 rounded-full bg-white border border-gray-200 shadow-sm flex items-center justify-center text-gray-600 hover:bg-gray-50"
        aria-label="Change profile picture"
      >
        {uploading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Camera className="h-3 w-3" />}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="hidden"
        onChange={handleFile}
      />
    </div>
  )
}
