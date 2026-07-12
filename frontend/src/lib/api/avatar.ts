// Profile picture upload. One multipart POST to the caller's own /me/avatar —
// the server derives the owner from the access token, so no id is sent, and it
// persists a storage object key (not an expiring signed URL) in the tenant DB.
import api from '@/lib/api'
import adminApi from '@/lib/adminApi'

const AVATAR_MIME_TYPES = ['image/jpeg', 'image/jpg', 'image/pjpeg', 'image/png', 'image/webp']
const AVATAR_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp']
const AVATAR_MAX_BYTES = 5 * 1024 * 1024

/** Browsers disagree on the MIME type for JPEG, and some report nothing at all
 * for WEBP, so fall back to the extension before rejecting a valid image. */
export const AVATAR_ACCEPT = '.jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp'

export class AvatarUploadError extends Error {}

/** True only for values that a browser can actually render as an <img src>.
 * Guards every avatar render site so a raw object key (or any other non-URL
 * string that might slip into avatarUrl) is NEVER shown as a broken image or
 * as literal text — the caller falls back to initials instead. */
export function isDisplayableImageUrl(value: string | null | undefined): value is string {
  if (!value) return false
  return /^(https?:\/\/|blob:|data:image\/|\/)/.test(value.trim())
}

function assertValidAvatar(file: File): void {
  const ext = file.name.includes('.') ? file.name.split('.').pop()!.toLowerCase() : ''
  const typeOk = AVATAR_MIME_TYPES.includes(file.type.toLowerCase())
  const extOk = AVATAR_EXTENSIONS.includes(ext)
  if (!typeOk && !extOk) {
    throw new AvatarUploadError('Please choose a JPG, JPEG, PNG, or WEBP image.')
  }
  if (file.size === 0) {
    throw new AvatarUploadError('That file is empty.')
  }
  if (file.size > AVATAR_MAX_BYTES) {
    throw new AvatarUploadError('Image must be 5MB or smaller.')
  }
}

/** Upload the signed-in user's profile picture. Returns the fresh viewable URL. */
export async function uploadMyAvatar(file: File): Promise<string | null> {
  assertValidAvatar(file)
  const form = new FormData()
  form.append('file', file, file.name)
  // Do NOT set Content-Type manually — the browser must compute the multipart
  // boundary itself, or the server cannot parse the body.
  const { data } = await api.post('/auth/me/avatar', form)
  return data.avatar_url ?? null
}

export async function removeMyAvatar(): Promise<void> {
  await api.delete('/auth/me/avatar')
}

/** Super admin equivalent — same validation, platform-scoped storage. */
export async function uploadPlatformAvatar(file: File): Promise<string | null> {
  assertValidAvatar(file)
  const form = new FormData()
  form.append('file', file, file.name)
  const { data } = await adminApi.post('/platform/auth/me/avatar', form)
  return data.avatar_url ?? null
}

export async function removePlatformAvatar(): Promise<void> {
  await adminApi.delete('/platform/auth/me/avatar')
}
