// Profile picture upload — presigned-URL flow via the storage module,
// followed by persisting the resolved URL on the user's own record.
import api from '@/lib/api'
import { generateUploadUrl, createAsset, getDownloadUrl } from '@/lib/api/storage'

const AVATAR_MIME_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const AVATAR_MAX_BYTES = 5 * 1024 * 1024

export class AvatarUploadError extends Error {}

/** True only for values that a browser can actually render as an <img src>.
 * Guards every avatar render site so a raw object key / asset UUID (or any
 * other non-URL string that might slip into avatar_url) is NEVER shown as a
 * broken image or as literal text — the caller falls back to initials instead. */
export function isDisplayableImageUrl(value: string | null | undefined): value is string {
  if (!value) return false
  return /^(https?:\/\/|blob:|data:image\/|\/)/.test(value.trim())
}

/** Upload a profile picture for `userId` (always the caller's own id — the
 * backend only allows self-service avatar updates) and return a viewable URL. */
export async function uploadAvatarFile(userId: string, file: File): Promise<string> {
  if (!AVATAR_MIME_TYPES.includes(file.type)) {
    throw new AvatarUploadError('Please choose a JPEG, PNG, or WebP image.')
  }
  if (file.size > AVATAR_MAX_BYTES) {
    throw new AvatarUploadError('Image must be 5MB or smaller.')
  }

  const { object_key, presigned_url } = await generateUploadUrl({
    entity_type: 'avatar',
    entity_id: userId,
    original_filename: file.name,
    content_type: file.type,
    size_bytes: file.size,
  })

  const putResp = await fetch(presigned_url, {
    method: 'PUT',
    headers: { 'Content-Type': file.type },
    body: file,
  })
  if (!putResp.ok) {
    // Without this guard a failed S3 upload was ignored and we went on to
    // persist an avatar URL pointing at a nonexistent object → broken image.
    throw new AvatarUploadError('Upload to storage failed. Please try again.')
  }

  const asset = await createAsset({
    object_key,
    entity_type: 'avatar',
    entity_id: userId,
    original_filename: file.name,
    content_type: file.type,
    size_bytes: file.size,
  })

  return getDownloadUrl(asset.id)
}

export async function updateMyAvatar(avatarUrl: string | null): Promise<void> {
  await api.patch('/auth/me/avatar', { avatar_url: avatarUrl })
}
